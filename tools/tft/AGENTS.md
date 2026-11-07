# The probe tool

These rules are for running the probes, and for research with the Nextion Editor. `README.md` describes the tool.

## Downloads

- Ask the user before downloading a release of the Nextion Editor, whether its zip or its installer.
- Never run an installer. It is downloaded only to read its hash.

## Scratch data

- **Keep it only while it is useful.** Probes, research scripts, and reviews write scratch data, such as projects, TFT files, and exported source trees. Delete it once the investigation in progress no longer needs it. Otherwise a long run of probes fills the disk.
- **Delete files one by one.** Delete each file by its full path, after checking that it is a regular file in the folder it was written to. Never delete with a wildcard, and never delete a whole folder.
- **Build every project under one file name,** such as `probe.HMI`. The Editor tool's `open` keeps a copy of each project it opens in its work folder, one copy for each file name. Projects with names of their own would fill that folder too.

## Long searches

These rules are for research searches and fits that may run for a long time.

- **Start with a pilot.** Before a large search, run a small one with a fixed bound. Measure how fast it goes, and estimate the rest of the work before expanding it.
- **Use the measurement.** Make the search smaller or faster with it. For example, narrow the cases searched, or move a search that would take more than a few minutes from Python to a compiled language such as Go.
- **Set a limit.** Give each exploratory search a limit on its run time or its work, and make it print its progress. Report the bounds searched, and whether the run finished. A search that was stopped, or that hit its limit, is not a negative result.
- **Make progress readable at any time.** Build progress monitoring in from the start, so that a run's state can be read without waiting for it to end. Check a run of unknown length after a couple of minutes.
