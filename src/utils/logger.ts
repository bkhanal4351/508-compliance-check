export type Logger = {
  info(message: string): void;
  warn(message: string): void;
  error(message: string): void;
  verbose(message: string): void;
};

export function createLogger(isVerbose: boolean): Logger {
  return {
    info: (message) => console.log(message),
    warn: (message) => console.warn(`Warning: ${message}`),
    error: (message) => console.error(`Error: ${message}`),
    verbose: (message) => {
      if (isVerbose) console.log(`Verbose: ${message}`);
    }
  };
}
