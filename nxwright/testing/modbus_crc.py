"""The checksum the screen's CRC commands compute: Modbus CRC16, the one
type the vendor's instruction set gives `crcrest`, worked out as the Nextion
Editor's simulator worked it out.

The running CRC is the 16-bit value `crcrest` starts and `crcputs` and
`crcputh` update, byte by byte. `crcval` reads it as a number from 0 to
65535. While no CRC runs, `crcval` reads CRC_OFF: after a `crcrest` of
another type, and in a simulation before any `crcrest`.
"""

# What `crcval` reads while no CRC runs.
CRC_OFF = -1
# Modbus CRC16's polynomial, 0x8005, its bits in the order the CRC takes them.
_POLYNOMIAL = 0xA001


def crc_start(value: int) -> int:
    """Returns the running CRC `crcrest 1,value` starts: the low 16 bits of
    `value`, in the opposite order, as Modbus CRC16 takes its bits. 0x1234
    starts 0x2C48, and -2, whose low 16 bits are 0xFFFE, starts 0x7FFF. The
    screen ignores a value above 65535, which the caller checks."""
    return int(format(value & 0xFFFF, "016b")[::-1], 2)


def crc_after(crc: int, data: bytes) -> int:
    """Returns the running CRC `crc` after the bytes `data`. A CRC that is
    off, CRC_OFF, stays off."""
    if crc == CRC_OFF:
        return crc
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ _POLYNOMIAL if crc & 1 else crc >> 1
    return crc
