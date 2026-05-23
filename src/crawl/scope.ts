export type ScopeOptions = {
  sameOrigin: boolean;
  sameHost: boolean;
};

export function isInScope(candidateUrl: string, startUrl: string, options: ScopeOptions): boolean {
  const candidate = new URL(candidateUrl);
  const start = new URL(startUrl);
  if (options.sameOrigin && candidate.origin !== start.origin) return false;
  if (options.sameHost && candidate.hostname !== start.hostname) return false;
  return true;
}
