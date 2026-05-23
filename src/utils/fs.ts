import fs from "fs-extra";
import path from "node:path";

export async function ensureOutputDirs(outDir: string): Promise<void> {
  await Promise.all([
    fs.ensureDir(outDir),
    fs.ensureDir(path.join(outDir, "raw", "web")),
    fs.ensureDir(path.join(outDir, "raw", "pdf")),
    fs.ensureDir(path.join(outDir, "downloads")),
    fs.ensureDir(path.join(outDir, "screenshots"))
  ]);
}

export function toPosixPath(filePath: string): string {
  return filePath.split(path.sep).join("/");
}
