import { SignUp } from "@clerk/nextjs";

const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

export default function SignUpPage() {
  if (!clerkEnabled) {
    return (
      <main className="auth-page">
        <div className="placeholder card">
          <div className="stack" style={{ textAlign: "center" }}>
            <span className="pill">Auth disabled locally</span>
            <h1>Clerk is not configured.</h1>
            <p className="muted">Add Clerk environment variables to enable sign-up.</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="auth-page">
      <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" fallbackRedirectUrl="/" />
    </main>
  );
}
