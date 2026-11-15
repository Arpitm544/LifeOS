import { SignUp } from "@clerk/nextjs";
import { Suspense } from "react";
import { AuthShell } from "@/components/layout/auth-layout";

export default function SignUpPage() {
  return (
    <AuthShell mode="sign-up">
      <Suspense fallback={<p role="status">Loading sign-up…</p>}>
        <SignUp appearance={{ elements: { headerTitle: { display: "none" }, headerSubtitle: { display: "none" }, rootBox: { width: "100%" }, cardBox: { width: "100%", maxWidth: "100%" } } }} routing="path" path="/sign-up" signInUrl="/sign-in" />
      </Suspense>
    </AuthShell>
  );
}
