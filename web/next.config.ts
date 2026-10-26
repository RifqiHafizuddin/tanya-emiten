import type { NextConfig } from "next";

// Crops are public-read WebP files in Supabase Storage (D11, D56); plain <img> tags, so no image domains to list.
const config: NextConfig = { reactStrictMode: true };
export default config;
