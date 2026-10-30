import { useEffect, useState } from "react";

function browserIsOnline(): boolean {
  return typeof navigator === "undefined" || navigator.onLine;
}

/** Suit l'état réseau annoncé par le navigateur sans effectuer de requête de contrôle. */
export function useConnectivity(): boolean {
  const [online, setOnline] = useState(browserIsOnline);

  useEffect(() => {
    const update = () => setOnline(browserIsOnline());
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  return online;
}
