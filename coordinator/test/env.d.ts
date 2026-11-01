import type { D1Migration } from "cloudflare:test";

declare global {
  namespace Cloudflare {
    interface Env {
      DB: D1Database;
      BUCKET: R2Bucket;
      ADMIN_TOKEN: string;
      MIN_CLIENT_VERSION: string;
      LEASE_TTL_SECONDS: string;
      MAX_ATTEMPTS: string;
      MAX_LEASE_JOBS: string;
      TEST_MIGRATIONS: D1Migration[];
    }
  }
}
export {};
