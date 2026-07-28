#!/usr/bin/env python3

import sys
import types

import smu_parts


class _SmuModule(types.ModuleType):
    def __setattr__(self, name, value):
        smu_parts.set_part_attribute(name, value)
        super().__setattr__(name, value)


globals().update(smu_parts.public_exports())
sys.modules[__name__].__class__ = _SmuModule


if __name__ == "__main__":
    main()
