import { createClient } from "@supabase/supabase-js";

// Defaults for ReTrace Community Cloud — these are publishable client-side keys,
// safe to commit. Override via VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY in .env.
const DEFAULTS = {
  url: "https://ndpkjdwupcvtglrqjfwr.supabase.co",
  anonKey: "sb_publishable_eBxTQwNWWEpKTi6tZb4xeA_QApk-h-l",
} as const;

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || DEFAULTS.url;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || DEFAULTS.anonKey;

export const supabase = supabaseUrl
  ? createClient(supabaseUrl, supabaseAnonKey)
  : null as unknown as ReturnType<typeof createClient>;

export const isSupabaseConfigured = () =>
  Boolean(supabaseUrl) && Boolean(supabaseAnonKey);
