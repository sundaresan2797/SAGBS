import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { useAuth } from "@/hooks/useAuth";
import { photoService } from "@/services/photoService";

interface PhotosContextValue {
  /** employee id -> version of their photo. A person with no photo is simply absent. */
  versions: Record<number, string>;
  /** Re-read who has a photo; call after a photo is added, changed or removed. */
  refresh: () => Promise<void>;
}

const PhotosContext = createContext<PhotosContextValue>({ versions: {}, refresh: async () => undefined });

// The pictures already fetched, by "id:version". A new version is a new key, so a changed photo is fetched
// again and an unchanged one is never fetched twice, however many screens show it.
const pictureCache = new Map<string, Promise<string>>();

function pictureUrl(employeeId: number, version: string): Promise<string> {
  const key = `${employeeId}:${version}`;
  let cached = pictureCache.get(key);
  if (!cached) {
    cached = photoService.fetchBlob(employeeId).then((blob) => URL.createObjectURL(blob));
    cached.catch(() => pictureCache.delete(key)); // a failed fetch may be retried later
    pictureCache.set(key, cached);
  }
  return cached;
}

export function PhotosProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [versions, setVersions] = useState<Record<number, string>>({});

  const refresh = useCallback(async () => {
    try {
      const entries = await photoService.index();
      setVersions(Object.fromEntries(entries.map((e) => [e.employee_id, e.photo_version])));
    } catch {
      // Photos are decoration: if the list can't be loaded, everyone simply shows their initials.
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) refresh();
    else setVersions({});
  }, [isAuthenticated, refresh]);

  const value = useMemo(() => ({ versions, refresh }), [versions, refresh]);
  return <PhotosContext.Provider value={value}>{children}</PhotosContext.Provider>;
}

export function usePhotos(): PhotosContextValue {
  return useContext(PhotosContext);
}

/** The photo to show for one employee: an image address, or null (no photo, or not loaded yet) -> show initials. */
export function useEmployeePhoto(employeeId: number | null | undefined): string | null {
  const { versions } = useContext(PhotosContext);
  const version = employeeId != null ? versions[employeeId] : undefined;
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (employeeId == null || !version) {
      setUrl(null);
      return;
    }
    let cancelled = false;
    pictureUrl(employeeId, version)
      .then((address) => {
        if (!cancelled) setUrl(address);
      })
      .catch(() => {
        if (!cancelled) setUrl(null);
      });
    return () => {
      cancelled = true;
    };
  }, [employeeId, version]);

  return url;
}
