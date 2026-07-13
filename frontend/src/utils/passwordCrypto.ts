const IV_LENGTH = 12;

function base64ToBytes(value: string) {
  const raw = atob(value);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) {
    bytes[i] = raw.charCodeAt(i);
  }
  return bytes;
}

function bytesToBase64(bytes: Uint8Array) {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

let cryptoKeyPromise: Promise<CryptoKey> | null = null;

async function getCryptoKey() {
  if (!cryptoKeyPromise) {
    cryptoKeyPromise = (async () => {
      const encoded = import.meta.env.VITE_PASSWORD_ENCRYPT_KEY?.trim();
      if (!encoded) {
        throw new Error("未配置密码加密密钥");
      }
      const keyBytes = base64ToBytes(encoded);
      return crypto.subtle.importKey("raw", keyBytes, "AES-GCM", false, ["encrypt"]);
    })();
  }
  return cryptoKeyPromise;
}

export async function encryptPassword(plain: string): Promise<string> {
  const key = await getCryptoKey();
  const iv = crypto.getRandomValues(new Uint8Array(IV_LENGTH));
  const encoded = new TextEncoder().encode(plain);
  const encrypted = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, encoded);
  const payload = new Uint8Array(iv.length + encrypted.byteLength);
  payload.set(iv);
  payload.set(new Uint8Array(encrypted), iv.length);
  return bytesToBase64(payload);
}
