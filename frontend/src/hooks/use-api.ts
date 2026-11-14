"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useMemo, useRef } from "react";
import { createApi } from "@/lib/api";

/** API client that sends the current Clerk session token as `Authorization: Bearer`. */
export function useApi() {
  const { getToken } = useAuth();
  const latest = useRef(getToken);
  useEffect(() => { latest.current = getToken; }, [getToken]);
  return useMemo(() => createApi(() => latest.current()), []);
}
