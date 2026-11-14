import { SignIn } from "@clerk/nextjs";
import { Suspense } from "react";
import { AuthShell } from "@/components/layout/auth-shell";

export default function SignInPage() {
  return (
    <AuthShell>
      <Suspense fallback={<p role="status">Loading sign-in…</p>}>
        <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" />
      </Suspense>
    </AuthShell>
  );
}
