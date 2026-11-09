"""The reasons a rule of the match check can give for refusing a value, each
written as the message a user reads. A rule gives its reason in
`refuses_because` (matching.Rule), and may give no other. A rule that takes
every value that fits in its bytes gives no reason.

  - INVALID_VALUE: the value has no meaning for its attribute, and
    nxwright's build refuses it first. The rule is a backstop that a user
    does not reach.
  - NOT_SUPPORTED_YET: the value has a known meaning that nxwright ought to
    write, but does not yet. Each such refusal is a gap in nxwright, filed as
    an nxwright bug.
  - DOES_NOT_FIT: the file stores the value in fewer bytes than it needs.

Rules of code give no reason. A line of code that no rule takes, or whose
characters past ASCII no rule takes, is refused as UNSUPPORTED_STATEMENT
instead, which asks the user to file a bug. When the compile starts from a
source folder, a line that nxwright's build refuses never reaches the
check. Any other refused line is one that the compile cannot write yet,
which is a gap in nxwright.
"""

INVALID_VALUE = "not a valid value for this attribute"
NOT_SUPPORTED_YET = "nxwright does not support this value yet"
DOES_NOT_FIT = "the value is outside the range that can be encoded"
REASONS = (INVALID_VALUE, NOT_SUPPORTED_YET, DOES_NOT_FIT)
UNSUPPORTED_STATEMENT = "unsupported statement, please file a bug"
