/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_COMPANY_NAME?: string;
  readonly VITE_POWERED_BY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
