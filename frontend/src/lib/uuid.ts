function randomSegment(): string {
  const value = Math.floor((1 + Math.random()) * 0x10000)
  return value.toString(16).slice(1)
}

export function createId(): string {
  const cryptoApi = globalThis.crypto as
    | {
        randomUUID?: () => string
        getRandomValues?: <T extends ArrayBufferView | null>(array: T) => T
      }
    | undefined

  if (cryptoApi?.randomUUID) {
    return cryptoApi.randomUUID()
  }

  if (cryptoApi?.getRandomValues) {
    const bytes = new Uint8Array(16)
    cryptoApi.getRandomValues(bytes)
    bytes[6] = (bytes[6] & 0x0f) | 0x40
    bytes[8] = (bytes[8] & 0x3f) | 0x80
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }

  return [
    randomSegment(),
    randomSegment(),
    randomSegment(),
    randomSegment(),
    randomSegment(),
    randomSegment(),
    randomSegment(),
    randomSegment(),
  ].join('')
}
