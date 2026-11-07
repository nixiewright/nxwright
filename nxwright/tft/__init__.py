"""TFT files, the files a Nextion screen runs: compiling a project into a
TFT file, decompiling a TFT file back into a source folder, and uploading a
TFT file to a screen over its serial port.

A TFT file contains the screen's firmware, which the vendor makes, and the
app's compiled pages, code, pictures, and fonts. The firmware is read at run
time, and never kept in nxwright (firmware.py).
"""
