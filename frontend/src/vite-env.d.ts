/// <reference types="vite/client" />

declare module "*.md?raw" {
  const content: string;
  export default content;
}

interface ImportMetaEnv {
  readonly VITE_REGISTRATION_ENABLED?: string;
  readonly VITE_PASSWORD_ENCRYPT_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
