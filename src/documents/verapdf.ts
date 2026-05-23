import path from "node:path";
import fs from "fs-extra";
import { commandExists, runCommand } from "../utils/command.js";

export async function runVeraPdfIfAvailable(filePath: string, outDir: string, timeoutMs: number): Promise<{ available: false } | { available: true; rawPath: string; output: string; exitCode: number | null }> {
  const available = await commandExists("verapdf");
  if (!available) return { available: false };
  const result = await runCommand("verapdf", ["--format", "text", filePath], timeoutMs);
  const rawPath = path.join(outDir, "raw", "pdf", `${path.basename(filePath)}.verapdf.txt`);
  await fs.writeFile(rawPath, `${result.stdout}\n${result.stderr}`);
  return { available: true, rawPath, output: `${result.stdout}\n${result.stderr}`, exitCode: result.code };
}
