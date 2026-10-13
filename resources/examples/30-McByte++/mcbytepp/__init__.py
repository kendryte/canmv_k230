# McByte++ for the Kendryte K230.
#
# A MicroPython port of the tracking pipeline from "Training-Free Long-Term
# Multi-Object Tracking for Sports Video Analytics" (Stanczyk, Yoon, Bremond;
# arXiv:2608.15688), https://github.com/tstanczyk95/McBytePlusPlus
#
# The association algorithm is ported faithfully.  The three learned components
# it leans on -- YOLOX-X, EdgeTAM, OSNet -- do not fit on this part and are
# replaced by on-device equivalents; each substitution is documented at the top
# of the module that makes it (detector.py, maskcue.py, reid.py, cmc.py).

__version__ = "1.0.0"
