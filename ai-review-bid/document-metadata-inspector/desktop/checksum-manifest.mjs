const CHECKSUM_RECORD = /^([0-9a-fA-F]{64})[ \t]+\*?([^/\\\r\n]+)$/u;

/**
 * Parse the one-record SHA256SUMS contract shared by build and runtime gates.
 *
 * @param {string} manifest
 * @param {string} executableName
 * @returns {string}
 */
export function expectedExecutableSha256(manifest, executableName) {
  const records = [];
  for (const line of manifest.split(/\r?\n/u)) {
    const trimmed = line.trim();
    if (trimmed.length === 0) {
      continue;
    }
    const match = CHECKSUM_RECORD.exec(trimmed);
    if (match?.[1] === undefined || match[2] === undefined) {
      throw new Error("Checksum manifest is invalid");
    }
    records.push({ hash: match[1].toLowerCase(), name: match[2] });
  }
  if (records.length !== 1 || records[0]?.name !== executableName) {
    throw new Error("Checksum manifest is invalid");
  }
  return records[0].hash;
}
