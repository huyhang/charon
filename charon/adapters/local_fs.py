import os
import shutil
import stat
from pathlib import Path, PurePosixPath


class LocalFileOps:
    def exists(self, path: PurePosixPath) -> bool:
        return Path(path).exists(follow_symlinks=False)

    def move(self, source: PurePosixPath, destination: PurePosixPath) -> None:
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(Path(source), Path(destination))

    def size(self, path: PurePosixPath) -> int:
        info = Path(path).lstat()
        if not stat.S_ISDIR(info.st_mode):
            return info.st_size
        return sum(
            (Path(folder) / name).lstat().st_size
            for folder, _, names in os.walk(path)
            for name in names
        )

    def resolve(self, path: PurePosixPath) -> PurePosixPath:
        return PurePosixPath(os.path.realpath(path))

    def list_folders(self, path: PurePosixPath) -> list[str]:
        with os.scandir(path) as entries:
            return sorted(entry.name for entry in entries if entry.is_dir())
