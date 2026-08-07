import posthog from "posthog-js";

const POSTHOG_KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY;
const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com";

export const posthogEnabled = Boolean(POSTHOG_KEY);

let initialized = false;

export function initPostHog() {
  if (!posthogEnabled || initialized || typeof window === "undefined") return;
  initialized = true;
  posthog.init(POSTHOG_KEY!, {
    api_host: POSTHOG_HOST,
    // Route pageviews through PostHogPageView (App Router navigations aren't
    // full page loads, so PostHog's own auto-pageview capture misses them).
    capture_pageview: false,
    // Don't create a full "person" profile (and count toward MAU billing)
    // for anonymous visitors — only once someone signs in and we identify().
    person_profiles: "identified_only",
  });
}

/** Safe to call unconditionally — no-ops when PostHog isn't configured. */
export function capture(event: string, properties?: Record<string, unknown>) {
  if (!posthogEnabled || typeof window === "undefined") return;
  posthog.capture(event, properties);
}

export { posthog };
