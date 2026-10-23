"""Block stamps: the checksum in the first 4 bytes of page blocks, page files,
and the manifest.

All use the same CRC: polynomial 0x04C11DB7, MSB first, starting at
0xFFFFFFFF, with every input byte fed as a 32-bit word holding that byte.
The CRC runs over the block after its stamp, then over ten more values:

  page block or page file: header bytes 4, 5, 6, 7, 12, 13, 14, 15, 20, 21
                           (the block size, the object count, and the
                           first two bytes of the word at byte 20)
  manifest:                header bytes 4, 5, 6, 7 (the header size), then
                           six values the Editor keeps for the project's
                           screen model outside the manifest; then the result
                           is XORed with a constant

The manifest's six values and constant are not known, but they are the same
for every manifest of a screen model, whatever its rotation, settings, or
resources. As the CRC is linear, their effect on the stamp is one number per
model: the model's stamp number. screen_models.py lists it for the Editor's
27 models. It can also be read off a manifest the Editor stamped, a
"reference", which is how a project of any model is stamped from its own
manifest.

Neither stamp is documented by the vendor; both were worked out from the
Editor's files, by way of the CRC described at
https://github.com/vladtsvetkov880-hub/nextion-hmi-format.
"""

POLYNOMIAL = 0x104C11DB7     # with the x^32 term, for reducing products
CRC_START = 0xFFFFFFFF
_PAGE_TAIL = (4, 5, 6, 7, 12, 13, 14, 15, 20, 21)
_MANIFEST_TAIL = (4, 5, 6, 7)
_MANIFEST_UNKNOWN_WORDS = 6


def multiply(a: int, b: int) -> int:
    """Multiplies two values as polynomials over GF(2), modulo POLYNOMIAL."""
    result = 0
    while b:
        if b & 1:
            result ^= a
        b >>= 1
        a <<= 1
        if a >> 32:
            a ^= POLYNOMIAL
    return result


def x_power(exponent: int) -> int:
    """Returns x to the power `exponent`, modulo POLYNOMIAL."""
    result, base = 1, 2
    while exponent:
        if exponent & 1:
            result = multiply(result, base)
        base = multiply(base, base)
        exponent >>= 1
    return result


# Feeding a 32-bit word w into register c gives (c ^ w) * x^32. These tables
# multiply each byte of (c ^ w) by its weight in one lookup.
_X32 = x_power(32)
_WORD_TABLES = [[multiply(byte << (8 * k), _X32) for byte in range(256)] for k in range(4)]


def word_crc(register: int, words) -> int:
    """Returns the CRC `register` after feeding it each 32-bit value of `words`."""
    table0, table1, table2, table3 = _WORD_TABLES
    for word in words:
        value = register ^ word
        register = (table0[value & 255] ^ table1[(value >> 8) & 255]
                    ^ table2[(value >> 16) & 255] ^ table3[value >> 24])
    return register


def _body_crc(block: bytes) -> int:
    """Returns the CRC register after every byte of `block` past its stamp."""
    return word_crc(CRC_START, memoryview(block)[4:])


def block_stamp(block: bytes) -> int:
    """Returns the stamp a page block or page file should carry."""
    return word_crc(_body_crc(block), [block[offset] for offset in _PAGE_TAIL])


def with_stamp(block: bytes) -> bytes:
    """Returns the page block or page file `block` with its stamp set."""
    return block_stamp(block).to_bytes(4, "little") + block[4:]


def manifest_stamp(block: bytes, reference: bytes) -> int:
    """Returns the stamp the manifest block ("main.HMI") `block` should carry.
    `reference` is a manifest of the same project, stamped by the Editor."""
    stored = int.from_bytes(reference[:4], "little")
    return _manifest_crc(block) ^ _manifest_crc(reference) ^ stored


def stamp_number(manifest: bytes) -> int:
    """Returns the stamp number of the model whose manifest `manifest` is,
    read off the stamp the Editor gave it."""
    return int.from_bytes(manifest[:4], "little") ^ _manifest_crc(manifest)


def with_model_manifest_stamp(block: bytes, number: int) -> bytes:
    """Returns the manifest block `block` with its stamp set, from its model's
    stamp number `number` (screen_models.py)."""
    return (_manifest_crc(block) ^ number).to_bytes(4, "little") + block[4:]


def _manifest_crc(block: bytes) -> int:
    """Returns the CRC over the manifest and its known tail values, with the
    unknown values left as zeros: their effect is the same for every manifest
    of a project."""
    tail = [block[offset] for offset in _MANIFEST_TAIL] + [0] * _MANIFEST_UNKNOWN_WORDS
    return word_crc(_body_crc(block), tail)


def with_manifest_stamp(block: bytes, reference: bytes) -> bytes:
    """Returns the manifest block `block` with its stamp set, using `reference`
    as manifest_stamp does."""
    return manifest_stamp(block, reference).to_bytes(4, "little") + block[4:]
