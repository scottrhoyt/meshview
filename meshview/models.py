from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, desc
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(AsyncAttrs, DeclarativeBase):
    pass


# Node
class Node(Base):
    __tablename__ = "node"
    id: Mapped[str] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(BigInteger, nullable=True, unique=True)
    long_name: Mapped[str] = mapped_column(nullable=True)
    short_name: Mapped[str] = mapped_column(nullable=True)
    hw_model: Mapped[str] = mapped_column(nullable=True)
    firmware: Mapped[str] = mapped_column(nullable=True)
    role: Mapped[str] = mapped_column(nullable=True)
    last_lat: Mapped[int] = mapped_column(BigInteger, nullable=True)
    last_long: Mapped[int] = mapped_column(BigInteger, nullable=True)
    channel: Mapped[str] = mapped_column(nullable=True)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_node_node_id", "node_id"),)

    def to_dict(self):
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
            if column.name != "last_update"
        }


class Packet(Base):
    __tablename__ = "packet"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    portnum: Mapped[int] = mapped_column(nullable=True)
    from_node_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    from_node: Mapped["Node"] = relationship(
        primaryjoin="Packet.from_node_id == foreign(Node.node_id)", lazy="joined"
    )
    to_node_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    to_node: Mapped["Node"] = relationship(
        primaryjoin="Packet.to_node_id == foreign(Node.node_id)",
        lazy="joined",
        overlaps="from_node",
    )
    payload: Mapped[bytes] = mapped_column(nullable=True)
    import_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    channel: Mapped[str] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_packet_from_node_id", "from_node_id"),
        Index("idx_packet_to_node_id", "to_node_id"),
        Index("idx_packet_import_time", desc("import_time")),
        # Composite index for /top endpoint performance - filters by from_node_id AND import_time
        Index("idx_packet_from_node_time", "from_node_id", desc("import_time")),
    )


class PacketSeen(Base):
    __tablename__ = "packet_seen"
    packet_id = mapped_column(ForeignKey("packet.id"), primary_key=True)
    node_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    node: Mapped["Node"] = relationship(
        lazy="joined",
        primaryjoin="PacketSeen.node_id == foreign(Node.node_id)",
        overlaps="from_node,to_node",
    )
    rx_time: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    hop_limit: Mapped[int] = mapped_column(nullable=True)
    hop_start: Mapped[int] = mapped_column(nullable=True)
    channel: Mapped[str] = mapped_column(nullable=True)
    rx_snr: Mapped[float] = mapped_column(nullable=True)
    rx_rssi: Mapped[int] = mapped_column(nullable=True)
    topic: Mapped[str] = mapped_column(nullable=True)
    import_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_packet_seen_node_id", "node_id"),
        # Index for /top endpoint performance - JOIN on packet_id
        Index("idx_packet_seen_packet_id", "packet_id"),
    )


class Traceroute(Base):
    __tablename__ = "traceroute"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    packet_id = mapped_column(ForeignKey("packet.id"))
    packet: Mapped["Packet"] = relationship(
        primaryjoin="Traceroute.packet_id == foreign(Packet.id)", lazy="joined"
    )
    gateway_node_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    done: Mapped[bool] = mapped_column(nullable=True)
    route: Mapped[bytes] = mapped_column(nullable=True)
    import_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_traceroute_import_time", "import_time"),)


class DeviceMetrics(Base):
    __tablename__ = "device_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    packet_id: Mapped[int] = mapped_column(ForeignKey("packet.id"), nullable=False)
    node_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    time: Mapped[int] = mapped_column(BigInteger, nullable=True)
    import_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    battery_level: Mapped[int] = mapped_column(nullable=True)
    voltage: Mapped[float] = mapped_column(nullable=True)
    channel_utilization: Mapped[float] = mapped_column(nullable=True)
    air_util_tx: Mapped[float] = mapped_column(nullable=True)
    uptime_seconds: Mapped[int] = mapped_column(nullable=True)
    channel: Mapped[str] = mapped_column(nullable=True)
    role: Mapped[str] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_device_metrics_node_id", "node_id"),
        Index("idx_device_metrics_import_time", desc("import_time")),
        Index("idx_device_metrics_node_time", "node_id", desc("import_time")),
    )


class EnvironmentMetrics(Base):
    __tablename__ = "environment_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    packet_id: Mapped[int] = mapped_column(ForeignKey("packet.id"), nullable=False)
    node_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    time: Mapped[int] = mapped_column(BigInteger, nullable=True)
    import_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    temperature: Mapped[float] = mapped_column(nullable=True)
    relative_humidity: Mapped[float] = mapped_column(nullable=True)
    barometric_pressure: Mapped[float] = mapped_column(nullable=True)
    gas_resistance: Mapped[float] = mapped_column(nullable=True)
    voltage: Mapped[float] = mapped_column(nullable=True)
    current: Mapped[float] = mapped_column(nullable=True)
    iaq: Mapped[int] = mapped_column(nullable=True)
    distance: Mapped[float] = mapped_column(nullable=True)
    lux: Mapped[float] = mapped_column(nullable=True)
    white_lux: Mapped[float] = mapped_column(nullable=True)
    ir_lux: Mapped[float] = mapped_column(nullable=True)
    uv_lux: Mapped[float] = mapped_column(nullable=True)
    wind_direction: Mapped[int] = mapped_column(nullable=True)
    wind_speed: Mapped[float] = mapped_column(nullable=True)
    wind_gust: Mapped[float] = mapped_column(nullable=True)
    wind_lull: Mapped[float] = mapped_column(nullable=True)
    weight: Mapped[float] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_environment_metrics_node_id", "node_id"),
        Index("idx_environment_metrics_import_time", desc("import_time")),
        Index("idx_environment_metrics_node_time", "node_id", desc("import_time")),
    )


class Position(Base):
    __tablename__ = "position"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    packet_id: Mapped[int] = mapped_column(ForeignKey("packet.id"), nullable=False)
    node_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Core coordinates (required)
    latitude_i: Mapped[int] = mapped_column(BigInteger, nullable=False)
    longitude_i: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Altitude fields
    altitude: Mapped[int] = mapped_column(nullable=True)
    altitude_hae: Mapped[int] = mapped_column(nullable=True)
    altitude_geoidal_separation: Mapped[int] = mapped_column(nullable=True)

    # Timing
    timestamp: Mapped[int] = mapped_column(BigInteger, nullable=True)
    timestamp_millis_adjust: Mapped[int] = mapped_column(nullable=True)
    import_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # GPS Quality/Accuracy metrics
    PDOP: Mapped[int] = mapped_column(nullable=True)
    HDOP: Mapped[int] = mapped_column(nullable=True)
    VDOP: Mapped[int] = mapped_column(nullable=True)
    gps_accuracy: Mapped[int] = mapped_column(nullable=True)
    fix_quality: Mapped[int] = mapped_column(nullable=True)
    fix_type: Mapped[int] = mapped_column(nullable=True)
    sats_in_view: Mapped[int] = mapped_column(nullable=True)

    # Movement data
    ground_speed: Mapped[int] = mapped_column(nullable=True)
    ground_track: Mapped[int] = mapped_column(nullable=True)

    # Source information
    location_source: Mapped[int] = mapped_column(nullable=True)
    altitude_source: Mapped[int] = mapped_column(nullable=True)

    # Additional metadata
    sensor_id: Mapped[int] = mapped_column(nullable=True)
    seq_number: Mapped[int] = mapped_column(nullable=True)
    precision_bits: Mapped[int] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_position_node_id", "node_id"),
        Index("idx_position_import_time", desc("import_time")),
        Index("idx_position_node_time", "node_id", desc("import_time")),
        Index("idx_position_packet_id", "packet_id"),
    )
