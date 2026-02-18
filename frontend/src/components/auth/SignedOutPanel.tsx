import { SignInButton } from "@/auth/clerk";

import { Button } from "@/components/ui/button";

type SignedOutPanelProps = {
  message: string;
  forceRedirectUrl: string;
  signUpForceRedirectUrl?: string;
  mode?: "modal" | "redirect";
  buttonLabel?: string;
  buttonTestId?: string;
};

export function SignedOutPanel({
  message,
  forceRedirectUrl,
  signUpForceRedirectUrl,
  mode = "modal",
  buttonLabel = "Sign in",
  buttonTestId,
}: SignedOutPanelProps) {
  return (
    <div className="col-span-2 flex min-h-[calc(100vh-64px)] items-center justify-center bg-slate-50 p-4 text-center sm:p-10">
      <div className="rounded-xl border border-slate-200 bg-white px-5 py-5 shadow-sm sm:px-8 sm:py-6">
        <p className="text-sm text-slate-600">{message}</p>
        <SignInButton
          mode={mode}
          forceRedirectUrl={forceRedirectUrl}
          signUpForceRedirectUrl={signUpForceRedirectUrl}
        >
          <Button className="mt-4" data-testid={buttonTestId}>
            {buttonLabel}
          </Button>
        </SignInButton>
      </div>
    </div>
  );
}
