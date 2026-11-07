"""The Nextion Editor versions whose firmware nxwright's probes were matched
with, and the SHA-256 hash of each of their firmware files.

A compile checks firmware of one of these versions against its hashes
(firmware.py), so that every file it packages is the one nxwright was matched
with. A hash is a fact about a file, not the file itself, so it may be kept
here: the vendor's files never are (AGENTS.md, The vendor's files).

This is the one list of matched versions. The match check's firmware rule
is built from it (packaging.py).
"""

# The hashes of 1.68.2 were read from its installed files, build 3035. A
# file that several series share, such as qr0.bin, is one file in the
# Nextion Editor's folder, so each name has one hash.
MATCHED_VERSIONS = {
    (1, 68, 2): {
        "3.cc": "9011d6f897da06c96261ba35e2de48c1db32b8c6eb3cb4bd3376947fa9d31a94",
        "6.cc": "a9248fb925fcb05f31e1fd4daca4f3f33d012fb837527e975f2dd3268abd3ea3",
        "asp0.dll": "17fad8f35e61f91cc16332512113b438fb7d2f0447c70120e361fb033fde2ec9",
        "asp1.dll": "17dcd1a8121ee76a5e1f08aa1f6d88de12f9966493a0727d37f644ddd374e91b",
        "asp100.dll": "3e508cf39f12bf7b244d5c016faabcb4ed5524f8790a9eba5824ae8dee85db06",
        "cd0.dll": "38b4d19cf15b626ec92e164b006ec782adf518b545a7dad953b6423f7a5cc3f8",
        "cd1.dll": "38b4d19cf15b626ec92e164b006ec782adf518b545a7dad953b6423f7a5cc3f8",
        "cd100.dll": "1a18652669af65d851f2c4e3b82fc4201beed9049dc4e524c32b3584500a71d3",
        "cdx.dll": "c25a5a12ad65229a9297257ab6f8d28957d63165d0c386fea92ca7d958f176d0",
        "h0-0.dll": "287d9b321491a29074491200174a543b340ac863aed8a707d7a82466979dbd39",
        "h0-1.dll": "287d9b321491a29074491200174a543b340ac863aed8a707d7a82466979dbd39",
        "h0-100.dll": "066fb0298ed928b13c206368b7e4c3bb38c183a6bdd747232ba48dba74a22989",
        "h1-0.dll": "f97b6206a6e3d784c2851f303fc29c5816309736b3fd4adc5f250cf8fa2196db",
        "h1-1.dll": "f97b6206a6e3d784c2851f303fc29c5816309736b3fd4adc5f250cf8fa2196db",
        "h1-100.dll": "e58945848d6889d690e7e6f9e569743314bfb8bef00e2d8332f989b926ba15dd",
        "input.bin": "34a2f19b8800c13ec13284e7db609012f46e70e68c08be00c2c20a395eb49304",
        "qr0.bin": "6750f8762fab464d45af4ab4d42ce565dd549af3f8b74a03127d6a4411e8ee27",
        "syscom.bin": "9276fdc48ad6e3676be5e4a1b68acb2b954253f18d6bc6a2dad31edbdc54590f",
    },
}


# The SHA-256 hash of each matched version's installer, as Nextion serves
# it. A download runs an installer only when its hash is here, as Nextion
# does not sign it (firmware_download.install_editor). 1.68.2's was read
# from nextion-setup-v1-68-2.exe, 51615016 bytes, downloaded from Nextion's
# site and never run.
INSTALLER_HASHES = {
    (1, 68, 2): "e5e121d00691ffaa0b344c61099fa511e3273b0e57c0f0f611e3ddab2b6edcaf",
}


def version_text(version: tuple) -> str:
    """Returns `version` as the Nextion Editor shows it, such as "1.68.2"."""
    return ".".join(str(part) for part in version)


def matched_versions_text() -> str:
    """Returns the matched versions as text for messages, oldest first, such
    as "1.68.2", or "1.68.2 or 1.70.0" if 1.70.0 were matched too."""
    return " or ".join(version_text(version) for version in sorted(MATCHED_VERSIONS))
