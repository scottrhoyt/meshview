import datetime
import re

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from meshtastic.protobuf.config_pb2 import Config
from meshtastic.protobuf.mesh_pb2 import HardwareModel
from meshtastic.protobuf.portnums_pb2 import PortNum
from meshview import decode_payload, mqtt_database
from meshview.models import DeviceMetrics, EnvironmentMetrics, Node, Packet, PacketSeen, Position, Traceroute


async def process_envelope(topic, env):
    # MAP_REPORT_APP
    if env.packet.decoded.portnum == PortNum.MAP_REPORT_APP:
        node_id = getattr(env.packet, "from")
        user_id = f"!{node_id:0{8}x}"

        map_report = decode_payload.decode_payload(
            PortNum.MAP_REPORT_APP, env.packet.decoded.payload
        )

        async with mqtt_database.async_session() as session:
            try:
                hw_model = (
                    HardwareModel.Name(map_report.hw_model)
                    if hasattr(HardwareModel, "Name")
                    else "unknown"
                )
                role = (
                    Config.DeviceConfig.Role.Name(map_report.role)
                    if hasattr(Config.DeviceConfig.Role, "Name")
                    else "unknown"
                )
                node = (
                    await session.execute(select(Node).where(Node.node_id == node_id))
                ).scalar_one_or_none()

                if node:
                    node.node_id = node_id
                    node.long_name = map_report.long_name
                    node.short_name = map_report.short_name
                    node.hw_model = hw_model
                    node.role = role
                    node.channel = env.channel_id
                    node.last_lat = map_report.latitude_i
                    node.last_long = map_report.longitude_i
                    node.firmware = map_report.firmware_version
                    node.last_update = datetime.datetime.now(datetime.UTC)
                else:
                    node = Node(
                        id=user_id,
                        node_id=node_id,
                        long_name=map_report.long_name,
                        short_name=map_report.short_name,
                        hw_model=hw_model,
                        role=role,
                        channel=env.channel_id,
                        firmware=map_report.firmware_version,
                        last_lat=map_report.latitude_i,
                        last_long=map_report.longitude_i,
                        last_update=datetime.datetime.now(datetime.UTC),
                    )
                    session.add(node)
            except Exception as e:
                print(f"Error processing MAP_REPORT_APP: {e}")

            await session.commit()

    if not env.packet.id:
        return

    async with mqtt_database.async_session() as session:
        # --- Packet insert (skip if already exists)
        result = await session.execute(select(Packet).where(Packet.id == env.packet.id))
        # FIXME: Not Used
        # new_packet = False
        packet = result.scalar_one_or_none()
        if not packet:
            # FIXME: Not Used
            # new_packet = True
            # Use a nested transaction (savepoint) for PostgreSQL compatibility
            async with session.begin_nested():
                try:
                    stmt = insert(Packet).values(
                        id=env.packet.id,
                        portnum=env.packet.decoded.portnum,
                        from_node_id=getattr(env.packet, "from"),
                        to_node_id=env.packet.to,
                        payload=env.packet.SerializeToString(),
                        import_time=datetime.datetime.now(datetime.UTC),
                        channel=env.channel_id,
                    )
                    await session.execute(stmt)
                    await session.flush()
                except IntegrityError:
                    # Packet was inserted by another process, ignore
                    pass

        # --- PacketSeen (no conflict handling here, normal insert)

        if not env.gateway_id:
            print("WARNING: Missing gateway_id, skipping PacketSeen entry")
            # Most likely a misconfiguration of a mqtt publisher?
            return
        else:
            node_id = int(env.gateway_id[1:], 16)

        result = await session.execute(
            select(PacketSeen).where(
                PacketSeen.packet_id == env.packet.id,
                PacketSeen.node_id == node_id,
                PacketSeen.rx_time == env.packet.rx_time,
            )
        )
        if not result.scalar_one_or_none():
            # Use a nested transaction (savepoint) so if PacketSeen insert fails,
            # we can rollback just this operation without affecting Packet insert
            async with session.begin_nested():
                try:
                    seen = PacketSeen(
                        packet_id=env.packet.id,
                        node_id=int(env.gateway_id[1:], 16),
                        channel=env.channel_id,
                        rx_time=env.packet.rx_time,
                        rx_snr=env.packet.rx_snr,
                        rx_rssi=env.packet.rx_rssi,
                        hop_limit=env.packet.hop_limit,
                        hop_start=env.packet.hop_start,
                        topic=topic,
                        import_time=datetime.datetime.now(datetime.UTC),
                    )
                    session.add(seen)
                    await session.flush()
                except IntegrityError:
                    # PacketSeen duplicate - already exists, ignore
                    pass

        # --- NODEINFO_APP handling
        if env.packet.decoded.portnum == PortNum.NODEINFO_APP:
            try:
                user = decode_payload.decode_payload(
                    PortNum.NODEINFO_APP, env.packet.decoded.payload
                )
                if user and user.id:
                    if user.id[0] == "!" and re.fullmatch(r"[0-9a-fA-F]+", user.id[1:]):
                        node_id = int(user.id[1:], 16)
                    else:
                        node_id = None

                    hw_model = (
                        HardwareModel.Name(user.hw_model)
                        if user.hw_model in HardwareModel.values()
                        else f"unknown({user.hw_model})"
                    )
                    role = (
                        Config.DeviceConfig.Role.Name(user.role)
                        if hasattr(Config.DeviceConfig.Role, "Name")
                        else "unknown"
                    )

                    node = (
                        await session.execute(select(Node).where(Node.id == user.id))
                    ).scalar_one_or_none()

                    if node:
                        node.node_id = node_id
                        node.long_name = user.long_name
                        node.short_name = user.short_name
                        node.hw_model = hw_model
                        node.role = role
                        node.channel = env.channel_id
                        node.last_update = datetime.datetime.now(datetime.UTC)
                    else:
                        node = Node(
                            id=user.id,
                            node_id=node_id,
                            long_name=user.long_name,
                            short_name=user.short_name,
                            hw_model=hw_model,
                            role=role,
                            channel=env.channel_id,
                            last_update=datetime.datetime.now(datetime.UTC),
                        )
                        session.add(node)
            except Exception as e:
                print(f"Error processing NODEINFO_APP: {e}")

        # --- POSITION_APP handling
        if env.packet.decoded.portnum == PortNum.POSITION_APP:
            try:
                position = decode_payload.decode_payload(
                    PortNum.POSITION_APP, env.packet.decoded.payload
                )
                if position and position.latitude_i and position.longitude_i:
                    from_node_id = getattr(env.packet, "from")
                    import_time = datetime.datetime.now(datetime.UTC)

                    # Update Node table with last known position (backward compatibility)
                    node = (
                        await session.execute(select(Node).where(Node.node_id == from_node_id))
                    ).scalar_one_or_none()
                    if node:
                        node.last_lat = position.latitude_i
                        node.last_long = position.longitude_i
                        session.add(node)

                    # Store full position history in Position table (with deduplication)
                    result = await session.execute(
                        select(Position).where(Position.packet_id == env.packet.id)
                    )
                    if not result.scalar_one_or_none():
                        session.add(
                            Position(
                                packet_id=env.packet.id,
                                node_id=from_node_id,
                                latitude_i=position.latitude_i,
                                longitude_i=position.longitude_i,
                                altitude=position.altitude if position.altitude else None,
                                altitude_hae=position.altitude_hae if position.altitude_hae else None,
                                altitude_geoidal_separation=position.altitude_geoidal_separation if position.altitude_geoidal_separation else None,
                                timestamp=position.timestamp if position.timestamp else None,
                                timestamp_millis_adjust=position.timestamp_millis_adjust if position.timestamp_millis_adjust else None,
                                import_time=import_time,
                                PDOP=position.PDOP if position.PDOP else None,
                                HDOP=position.HDOP if position.HDOP else None,
                                VDOP=position.VDOP if position.VDOP else None,
                                gps_accuracy=position.gps_accuracy if position.gps_accuracy else None,
                                fix_quality=position.fix_quality if position.fix_quality else None,
                                fix_type=position.fix_type if position.fix_type else None,
                                sats_in_view=position.sats_in_view if position.sats_in_view else None,
                                ground_speed=position.ground_speed if position.ground_speed else None,
                                ground_track=position.ground_track if position.ground_track else None,
                                location_source=position.location_source if position.location_source else None,
                                altitude_source=position.altitude_source if position.altitude_source else None,
                                sensor_id=position.sensor_id if position.sensor_id else None,
                                seq_number=position.seq_number if position.seq_number else None,
                                precision_bits=position.precision_bits if position.precision_bits else None,
                            )
                        )
            except Exception as e:
                print(f"Error processing POSITION_APP: {e}")

        # --- TRACEROUTE_APP (no conflict handling, normal insert)
        if env.packet.decoded.portnum == PortNum.TRACEROUTE_APP:
            packet_id = None
            if env.packet.decoded.want_response:
                packet_id = env.packet.id
            else:
                result = await session.execute(
                    select(Packet).where(Packet.id == env.packet.decoded.request_id)
                )
                if result.scalar_one_or_none():
                    packet_id = env.packet.decoded.request_id
            if packet_id is not None:
                session.add(
                    Traceroute(
                        packet_id=packet_id,
                        route=env.packet.decoded.payload,
                        done=not env.packet.decoded.want_response,
                        gateway_node_id=int(env.gateway_id[1:], 16),
                        import_time=datetime.datetime.now(datetime.UTC),
                    )
                )

        # --- TELEMETRY_APP (decode and store in dedicated tables)
        if env.packet.decoded.portnum == PortNum.TELEMETRY_APP:
            try:
                telemetry = decode_payload.decode_payload(
                    PortNum.TELEMETRY_APP, env.packet.decoded.payload
                )
                if telemetry:
                    from_node_id = getattr(env.packet, "from")
                    import_time = datetime.datetime.now(datetime.UTC)

                    # Look up node's role for telemetry records
                    node = (
                        await session.execute(select(Node).where(Node.node_id == from_node_id))
                    ).scalar_one_or_none()
                    node_role = node.role if node else None

                    # Check which metric type is present
                    if telemetry.HasField('device_metrics'):
                        # Check if DeviceMetrics already exists for this packet
                        result = await session.execute(
                            select(DeviceMetrics).where(DeviceMetrics.packet_id == env.packet.id)
                        )
                        if not result.scalar_one_or_none():
                            device = telemetry.device_metrics
                            session.add(
                                DeviceMetrics(
                                    packet_id=env.packet.id,
                                    node_id=from_node_id,
                                    time=telemetry.time if telemetry.time else None,
                                    import_time=import_time,
                                    battery_level=device.battery_level if device.battery_level else None,
                                    voltage=device.voltage if device.voltage else None,
                                    channel_utilization=device.channel_utilization if device.channel_utilization else None,
                                    air_util_tx=device.air_util_tx if device.air_util_tx else None,
                                    uptime_seconds=device.uptime_seconds if device.uptime_seconds else None,
                                    channel=env.channel_id,
                                    role=node_role,
                                )
                            )

                    if telemetry.HasField('environment_metrics'):
                        # Check if EnvironmentMetrics already exists for this packet
                        result = await session.execute(
                            select(EnvironmentMetrics).where(EnvironmentMetrics.packet_id == env.packet.id)
                        )
                        if not result.scalar_one_or_none():
                            env_metrics = telemetry.environment_metrics
                            session.add(
                                EnvironmentMetrics(
                                    packet_id=env.packet.id,
                                    node_id=from_node_id,
                                    time=telemetry.time if telemetry.time else None,
                                    import_time=import_time,
                                    temperature=env_metrics.temperature if env_metrics.temperature else None,
                                    relative_humidity=env_metrics.relative_humidity if env_metrics.relative_humidity else None,
                                    barometric_pressure=env_metrics.barometric_pressure if env_metrics.barometric_pressure else None,
                                    gas_resistance=env_metrics.gas_resistance if env_metrics.gas_resistance else None,
                                    voltage=env_metrics.voltage if env_metrics.voltage else None,
                                    current=env_metrics.current if env_metrics.current else None,
                                    iaq=env_metrics.iaq if env_metrics.iaq else None,
                                    distance=env_metrics.distance if env_metrics.distance else None,
                                    lux=env_metrics.lux if env_metrics.lux else None,
                                    white_lux=env_metrics.white_lux if env_metrics.white_lux else None,
                                    ir_lux=env_metrics.ir_lux if env_metrics.ir_lux else None,
                                    uv_lux=env_metrics.uv_lux if env_metrics.uv_lux else None,
                                    wind_direction=env_metrics.wind_direction if env_metrics.wind_direction else None,
                                    wind_speed=env_metrics.wind_speed if env_metrics.wind_speed else None,
                                    wind_gust=env_metrics.wind_gust if env_metrics.wind_gust else None,
                                    wind_lull=env_metrics.wind_lull if env_metrics.wind_lull else None,
                                    weight=env_metrics.weight if env_metrics.weight else None,
                                )
                            )
            except Exception as e:
                print(f"Error processing TELEMETRY_APP: {e}")

        await session.commit()

        # if new_packet:
        #    await packet.awaitable_attrs.to_node
        #    await packet.awaitable_attrs.from_node
