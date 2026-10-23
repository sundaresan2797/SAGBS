// The company name shown on the login page and browser tab. Set VITE_COMPANY_NAME in frontend/.env.
export const COMPANY_NAME = import.meta.env.VITE_COMPANY_NAME?.trim() || "Employee Portal";

// The software provider credited in "Powered by ..." lines. Set VITE_POWERED_BY in frontend/.env (leave empty to hide it).
export const POWERED_BY = import.meta.env.VITE_POWERED_BY?.trim() ?? "";
