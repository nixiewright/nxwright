"""Why a rule of the match check refuses a value: the only reasons it may
give (matching.Rule, its refuses_because), each as the message a user
reads. A rule that takes every value that fits in its bytes gives none.

  - INVALID_VALUE: the value has no meaning for its attribute, and
    nxwright's build refuses it first. The rule is a backstop that a user
    does not reach.
  - NOT_SUPPORTED_YET: the value has a known meaning that nxwright ought to
    write, but does not yet. Each such refusal is a gap in nxwright, filed as
    an nxwright bug.
  - DOES_NOT_FIT: the file stores the value in fewer bytes than it needs.
"""

INVALID_VALUE = "not a valid value for this attribute"
NOT_SUPPORTED_YET = "nxwright does not support this value yet"
DOES_NOT_FIT = "the value is outside the range that can be encoded"
REASONS = (INVALID_VALUE, NOT_SUPPORTED_YET, DOES_NOT_FIT)
