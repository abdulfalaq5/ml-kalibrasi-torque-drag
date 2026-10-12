import { useQuery } from "@tanstack/react-query";
import { api, UserItem } from "./api";

export type Me = { username: string; role: "admin" | "guest" };

export const fetchMe = () => api.get<Me>("/api/auth/me");

/** Guest account (K-45): Monitoring + Dashboard only, charts show only actual and ML / prediction. */
export function useIsGuest(): boolean {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    staleTime: Infinity,
  });
  return me.data?.role === "guest";
}

/** Accounts (admin only, K-47): used to choose / change the owner of a monitoring well. */
export function useUsers(enabled: boolean) {
  return useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserItem[]>("/api/users"),
    enabled,
  });
}
