"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Menu } from "lucide-react";

import { SignedIn, useAuth } from "@/auth/clerk";

import { ApiError } from "@/api/mutator";
import {
  type getMeApiV1UsersMeGetResponse,
  useGetMeApiV1UsersMeGet,
} from "@/api/generated/users/users";
import { BrandMark } from "@/components/atoms/BrandMark";
import { OrgSwitcher } from "@/components/organisms/OrgSwitcher";
import { UserMenu } from "@/components/organisms/UserMenu";
import { isOnboardingComplete } from "@/lib/onboarding";

export type MobileSidebarContext = {
  isOpen: boolean;
  toggle: () => void;
  close: () => void;
};

export function DashboardShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { isSignedIn } = useAuth();
  const isOnboardingPath = pathname === "/onboarding";
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const meQuery = useGetMeApiV1UsersMeGet<
    getMeApiV1UsersMeGetResponse,
    ApiError
  >({
    query: {
      enabled: Boolean(isSignedIn) && !isOnboardingPath,
      retry: false,
      refetchOnMount: "always",
    },
  });
  const profile = meQuery.data?.status === 200 ? meQuery.data.data : null;
  const displayName = profile?.name ?? profile?.preferred_name ?? "Operator";
  const displayEmail = profile?.email ?? "";

  useEffect(() => {
    if (!isSignedIn || isOnboardingPath) return;
    if (!profile) return;
    if (!isOnboardingComplete(profile)) {
      router.replace("/onboarding");
    }
  }, [isOnboardingPath, isSignedIn, profile, router]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleStorage = (event: StorageEvent) => {
      if (event.key !== "openclaw_org_switch" || !event.newValue) return;
      window.location.reload();
    };

    window.addEventListener("storage", handleStorage);

    let channel: BroadcastChannel | null = null;
    if ("BroadcastChannel" in window) {
      channel = new BroadcastChannel("org-switch");
      channel.onmessage = () => {
        window.location.reload();
      };
    }

    return () => {
      window.removeEventListener("storage", handleStorage);
      channel?.close();
    };
  }, []);

  // Close sidebar on route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  const closeSidebar = useCallback(() => setSidebarOpen(false), []);
  const toggleSidebar = useCallback(
    () => setSidebarOpen((prev) => !prev),
    [],
  );

  return (
    <MobileSidebarProvider
      value={{ isOpen: sidebarOpen, toggle: toggleSidebar, close: closeSidebar }}
    >
      <div className="min-h-screen bg-app text-strong">
        <header className="sticky top-0 z-40 border-b border-slate-200 bg-white shadow-sm">
          <div className="flex items-center gap-0 py-3 md:grid md:grid-cols-[260px_1fr_auto]">
            {/* Hamburger - mobile only */}
            <button
              type="button"
              onClick={toggleSidebar}
              className="ml-3 rounded-lg p-2 text-slate-600 hover:bg-slate-100 md:hidden"
              aria-label="Toggle navigation"
            >
              <Menu className="h-5 w-5" />
            </button>
            {/* Brand - hidden on mobile (save space), shown on desktop */}
            <div className="hidden items-center px-6 md:flex">
              <BrandMark />
            </div>
            {/* Org switcher */}
            <SignedIn>
              <div className="flex flex-1 items-center md:flex-none">
                <div className="max-w-[220px]">
                  <OrgSwitcher />
                </div>
              </div>
            </SignedIn>
            {/* User menu */}
            <SignedIn>
              <div className="flex items-center gap-3 px-4 md:px-6">
                <div className="hidden text-right lg:block">
                  <p className="text-sm font-semibold text-slate-900">
                    {displayName}
                  </p>
                  <p className="text-xs text-slate-500">Operator</p>
                </div>
                <UserMenu displayName={displayName} displayEmail={displayEmail} />
              </div>
            </SignedIn>
          </div>
        </header>
        <div className="grid min-h-[calc(100vh-64px)] grid-cols-1 bg-slate-50 md:grid-cols-[260px_1fr]">
          {children}
        </div>
      </div>
    </MobileSidebarProvider>
  );
}

// Context for sidebar state so children can access it
import { createContext, useContext } from "react";

const MobileSidebarCtx = createContext<MobileSidebarContext>({
  isOpen: false,
  toggle: () => {},
  close: () => {},
});

function MobileSidebarProvider({
  children,
  value,
}: {
  children: ReactNode;
  value: MobileSidebarContext;
}) {
  return (
    <MobileSidebarCtx.Provider value={value}>
      {children}
    </MobileSidebarCtx.Provider>
  );
}

export function useMobileSidebar() {
  return useContext(MobileSidebarCtx);
}
