import dataclasses
import enum
import json
import logging
import os

from gitfourchette import pycompat  # StrEnum for Python 3.10
from gitfourchette.porcelain import *
from gitfourchette.qt import *

logger = logging.getLogger(__name__)


class PrefsJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
            return {"_type": "bytes", "data": obj.hex()}
        elif isinstance(obj, Signature):
            return { "_type": "Signature", "name": obj.name, "email": obj.email, "time": obj.time, "offset": obj.offset }
        elif isinstance(obj, set):
            return list(obj)
        return super().default(obj)


class PrefsJSONDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, j):
        if '_type' not in j:
            return j
        type = j['_type']
        if type == "bytes":
            return bytes.fromhex(j["data"])
        elif type == "Signature":
            return Signature(j["name"], j["email"], j["time"], j["offset"])
        return j


class PrefsFile:
    _filename = ""
    _allowMakeDirs = True

    def getParentDir(self):
        from gitfourchette.settings import TEST_MODE
        if TEST_MODE:
            return os.path.join(qTempDir(), "testmode-config")
        return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)

    def _getFullPath(self, forWriting: bool):
        assert self._filename != "", "you must override _filename"

        prefsDir = self.getParentDir()
        if not prefsDir:
            return None

        if forWriting:
            if self._allowMakeDirs or False:
                os.makedirs(prefsDir, exist_ok=True)
            elif not os.path.isdir(prefsDir):
                return None

        fullPath = os.path.join(prefsDir, self._filename)

        if not forWriting and not os.path.isfile(fullPath):
            return None

        return fullPath

    def setDirty(self):
        self._dirty = True

    def isDirty(self):
        try:
            return self._dirty
        except AttributeError:
            return False

    def write(self, force=False):
        # Prepare the path
        prefsPath = self._getFullPath(forWriting=True)
        if not prefsPath:
            logger.warning("Couldn't get path for writing")
            return None

        # Get default values if we're saving a dataclass
        defaults = {}
        if dataclasses.is_dataclass(self):
            for f in dataclasses.fields(self):
                if f.default_factory != dataclasses.MISSING:
                    defaults[f.name] = f.default_factory()
                else:
                    defaults[f.name] = f.default

        # Skip private fields starting with an underscore,
        # and skip fields that are set to the default value
        filtered = {}
        for k in self.__dict__:
            if k.startswith("_"):
                continue
            v = self.__dict__[k]
            if (k not in defaults) or (defaults[k] != v):
                if isinstance(v, enum.Enum):  # Convert Qt enums to plain old data type
                    v = v.value
                filtered[k] = v

        # If the filtered object comes out empty (all defaults)
        # avoid cluttering the directory - don't write out an empty object
        if not filtered:
            if not self._getFullPath(forWriting=False):
                # File doesn't exist - don't write out an empty object
                logger.debug("Not writing empty object")
            else:
                logger.debug("Deleting prefs file because we want defaults")
                os.unlink(prefsPath)
            return None

        # Dump the object to disk
        with open(prefsPath, 'wt', encoding='utf-8') as jsonFile:
            json.dump(obj=filtered, fp=jsonFile, indent='\t', cls=PrefsJSONEncoder)

        self._dirty = False

        logger.info(f"Wrote {prefsPath}")
        return prefsPath

    def load(self):
        prefsPath = self._getFullPath(forWriting=False)
        if not prefsPath:  # couldn't be found
            return False

        with open(prefsPath, 'rt', encoding='utf-8') as f:
            try:
                obj = json.load(f, cls=PrefsJSONDecoder)
            except ValueError as loadError:
                logger.warning(f"{prefsPath}: {loadError}", exc_info=True)
                return False

            for k in obj:
                if k.startswith('_'):
                    logger.warning(f"{prefsPath}: skipping illegal key: {k}")
                    continue
                if k not in self.__dict__:
                    logger.warning(f"{prefsPath}: skipping unknown key: {k}")
                    continue

                if obj[k] is None:
                    continue

                originalType = self.__dataclass_fields__[k].type
                if issubclass(originalType, enum.StrEnum):
                    acceptedType = str
                elif issubclass(originalType, (enum.IntEnum, enum.Enum)):
                    acceptedType = int
                elif issubclass(originalType, set):
                    acceptedType = list
                else:
                    acceptedType = originalType

                if acceptedType is not originalType:
                    assert isinstance(obj[k], acceptedType)
                    self.__dict__[k] = originalType(obj[k])
                else:
                    self.__dict__[k] = obj[k]

        self._dirty = False
        return True
