import os
import shutil
from pathlib import Path, PurePosixPath


class LocalFileOps:
    def exists(self, path: PurePosixPath) -> bool:
        return Path(path).exists(follow_symlinks=False)

    def move(self, source: PurePosixPath, destination: PurePosixPath) -> None:
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(Path(source), Path(destination))

    def resolve(self, path: PurePosixPath) -> PurePosixPath:
        return PurePosixPath(os.path.realpath(path))

    def list_folders(self, path: PurePosixPath) -> list[str]:
        with os.scandir(path) as entries:
            return sorted(entry.name for entry in entries if entry.is_dir())
