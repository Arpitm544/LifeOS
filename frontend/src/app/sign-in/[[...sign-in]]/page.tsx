import { SignIn } from "@clerk/nextjs";
import { Suspense } from "react";
import { AuthShell } from "@/components/layout/auth-layout";

export default function SignInPage() {
  return (
    <AuthShell mode="sign-in">
      <Suspense fallback={<p role="status">Loading sign-in…</p>}>
        <SignIn appearance={{ elements: { headerTitle: { display: "none" }, headerSubtitle: { display: "none" }, rootBox: { width: "100%" }, cardBox: { width: "100%", maxWidth: "100%" } } }} routing="path" path="/sign-in" signUpUrl="/sign-up" />
      </Suspense>
    </AuthShell>
  );
}
