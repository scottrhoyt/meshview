import asyncio
import base64
import logging
import random
import time

import aiomqtt
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from google.protobuf.message import DecodeError

from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from meshview.config import CONFIG

# Default Meshtastic encryption key
DEFAULT_KEY = base64.b64decode("1PG7OiApB1nwvP+rz05pAQ==")

# Load channel-specific encryption keys from config
# Note: ConfigParser lowercases keys, so we store with lowercase for case-insensitive lookup
CHANNEL_KEYS = {}
for channel_name, key_b64 in CONFIG.get('channels', {}).items():
    try:
        key_bytes = base64.b64decode(key_b64)
        if len(key_bytes) not in (16, 32):
            logging.warning(
                f"Invalid key length for channel '{channel_name}': "
                f"{len(key_bytes)} bytes (must be 16 or 32)"
            )
            continue
        # Store with lowercase key for case-insensitive matching
        CHANNEL_KEYS[channel_name.lower()] = key_bytes
    except Exception as e:
        logging.warning(f"Failed to load key for channel '{channel_name}': {e}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(filename)s:%(lineno)d [pid:%(process)d] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def decrypt(packet, channel_id=None):
    if packet.HasField("decoded"):
        return

    packet_id = packet.id.to_bytes(8, "little")
    from_node_id = getattr(packet, "from").to_bytes(8, "little")
    nonce = packet_id + from_node_id

    # Build list of keys to try: channel-specific first, then default
    keys_to_try = []
    if channel_id:
        # Case-insensitive lookup since ConfigParser lowercases keys
        channel_key = CHANNEL_KEYS.get(channel_id.lower())
        if channel_key:
            keys_to_try.append(channel_key)
    keys_to_try.append(DEFAULT_KEY)

    for key in keys_to_try:
        cipher = Cipher(algorithms.AES(key), modes.CTR(nonce))
        decryptor = cipher.decryptor()
        raw_proto = decryptor.update(packet.encrypted) + decryptor.finalize()
        try:
            packet.decoded.ParseFromString(raw_proto)
            if packet.HasField("decoded") and packet.decoded.portnum:
                return  # Successfully decoded with valid portnum
        except DecodeError:
            continue  # Try next key

    # If we get here, none of the keys worked - clear any partial decode
    packet.decoded.Clear()


async def get_topic_envelopes(mqtt_server, mqtt_port, topics, mqtt_user, mqtt_passwd):
    identifier = str(random.getrandbits(16))
    msg_count = 0
    start_time = None
    while True:
        try:
            async with aiomqtt.Client(
                mqtt_server,
                port=mqtt_port,
                username=mqtt_user,
                password=mqtt_passwd,
                identifier=identifier,
            ) as client:
                logger.info(f"Connected to MQTT broker at {mqtt_server}:{mqtt_port}")
                for topic in topics:
                    logger.info(f"Subscribing to: {topic}")
                    await client.subscribe(topic)

                # Reset start time when connected
                if start_time is None:
                    start_time = time.time()

                async for msg in client.messages:
                    try:
                        envelope = ServiceEnvelope.FromString(msg.payload)
                    except DecodeError:
                        continue

                    decrypt(envelope.packet, envelope.channel_id)
                    # print(envelope.packet.decoded)
                    if not envelope.packet.decoded:
                        continue

                    # Skip packets from specific node
                    # FIXME: make this configurable as a list of node IDs to skip
                    if getattr(envelope.packet, "from", None) == 2144342101:
                        continue

                    msg_count += 1
                    # FIXME: make this interval configurable or time based
                    if (
                        msg_count % 10000 == 0
                    ):  # Log notice every 10000 messages (approx every hour at 3/sec)
                        elapsed_time = time.time() - start_time
                        msg_rate = msg_count / elapsed_time if elapsed_time > 0 else 0
                        logger.info(
                            f"Processed {msg_count} messages so far... ({msg_rate:.2f} msg/sec)"
                        )

                    yield msg.topic.value, envelope

        except aiomqtt.MqttError as e:
            logger.error(f"MQTT error: {e}, reconnecting in 1s...")
            await asyncio.sleep(1)
