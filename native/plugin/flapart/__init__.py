# SPDX-License-Identifier: GPL-3.0-or-later
from .studio import FlapartStudio
from krita import Krita
Krita.instance().addExtension(FlapartStudio(Krita.instance()))
