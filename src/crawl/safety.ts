import dns from "node:dns/promises";
import net from "node:net";

function ipv4ToNumber(ip: string): number {
  return ip.split(".").reduce((acc, part) => (acc << 8) + Number(part), 0) >>> 0;
}

function isIpv4InCidr(ip: string, base: string, prefix: number): boolean {
  const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0;
  return (ipv4ToNumber(ip) & mask) === (ipv4ToNumber(base) & mask);
}

export function isPrivateOrLocalIp(ip: string): boolean {
  if (ip === "0.0.0.0" || ip === "169.254.169.254") return true;
  if (net.isIPv4(ip)) {
    return (
      isIpv4InCidr(ip, "127.0.0.0", 8) ||
      isIpv4InCidr(ip, "10.0.0.0", 8) ||
      isIpv4InCidr(ip, "172.16.0.0", 12) ||
      isIpv4InCidr(ip, "192.168.0.0", 16) ||
      isIpv4InCidr(ip, "169.254.0.0", 16)
    );
  }
  const lower = ip.toLowerCase();
  return lower === "::1" || lower.startsWith("fc") || lower.startsWith("fd") || lower.startsWith("fe80:");
}

export async function assertUrlIsSafe(url: string): Promise<{ safe: true } | { safe: false; reason: string }> {
  const hostname = new URL(url).hostname;
  if (hostname === "localhost") return { safe: false, reason: "Blocked localhost hostname" };
  if (net.isIP(hostname) && isPrivateOrLocalIp(hostname)) {
    return { safe: false, reason: `Blocked private/internal IP ${hostname}` };
  }

  try {
    const records = await dns.lookup(hostname, { all: true, verbatim: true });
    const blocked = records.find((record) => isPrivateOrLocalIp(record.address));
    if (blocked) {
      return { safe: false, reason: `Blocked hostname resolving to private/internal IP ${blocked.address}` };
    }
    return { safe: true };
  } catch (error) {
    return { safe: false, reason: `Could not resolve hostname for safety check: ${String(error)}` };
  }
}
