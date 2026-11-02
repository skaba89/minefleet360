import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { saveFieldProfile } from "../lib/offlineFieldProfile";
import { can } from "../lib/permissions";

type Site = Schemas["SiteOut"];

interface SiteState {
  sites: Site[];
  /** Site sélectionné ; null = tous les sites de ma portée. */
  siteId: string | null;
  setSiteId: (id: string | null) => void;
  /** Fuseau d'affichage d'un site (celui du site, sinon celui de la société : H4). */
  timezoneOf: (siteId: string | null | undefined) => string;
}

const SiteContext = createContext<SiteState | null>(null);

export function SiteProvider({ children }: { children: ReactNode }) {
  const me = useMe();
  const [siteId, setSiteId] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: ["sites"],
    enabled: can(me.grants, "organization.site.read"),
    queryFn: () => read("/sites", { query: { page_size: 200 } }),
  });
  // Profil terrain pour une ouverture sans réseau : seulement les sites où le compte peut déclarer.
  useEffect(() => {
    if (!data) return;
    saveFieldProfile({
      workspace_code: me.workspace_code,
      user_account_id: me.user_account_id,
      display_name: me.display_name,
      timezone: me.timezone,
      sites: data.items
        .filter((s) => can(me.grants, "hse.incident.report", s.site_id))
        .map((s) => ({ site_id: s.site_id, code: s.code, name: s.name, timezone: s.timezone ?? null })),
    });
  }, [data, me]);
  const value = useMemo<SiteState>(() => {
    const sites = data?.items ?? [];
    const byId = new Map(sites.map((s) => [s.site_id, s]));
    return {
      sites,
      siteId,
      setSiteId,
      timezoneOf: (id) => (id && byId.get(id)?.timezone) || me.timezone,
    };
  }, [data, siteId, me.timezone]);
  return <SiteContext.Provider value={value}>{children}</SiteContext.Provider>;
}

export function useSites(): SiteState {
  const ctx = useContext(SiteContext);
  if (!ctx) throw new Error("useSites hors de SiteProvider");
  return ctx;
}
