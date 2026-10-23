"""The debug adapter: VS Code's debugger for the screen code a test runs,
served by `nxwright debug-adapter` (adapter.py).
  - adapter.py speaks the Debug Adapter Protocol, and runs the test with
    recording on (testing/recording.py).
  - replay.py moves through the recording, forward and backward.
"""
