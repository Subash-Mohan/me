/**
 * Best-effort device location capture for chat sends.
 *
 * Single export: `getCurrentLocation()`. Returns `{lat, lng}` when the user
 * has granted foreground permission and a fix arrives within the timeout;
 * `null` otherwise. The send pipeline never blocks visibly: the internal
 * timeout caps cold-start latency at 1.5s, and a module-level cache
 * (120s TTL) makes warm sends instant.
 *
 * We deliberately do NOT reverse-geocode here. The human-readable place
 * name lives in the user's message text and the agent extracts it onto
 * memory rows; a device-side label would be redundant.
 */

import * as Location from "expo-location";

export type ClientLocation = { lat: number; lng: number };

const TTL_MS = 120_000;
const TIMEOUT_MS = 1500;
let cache: { value: ClientLocation; at: number } | null = null;
let permanentlyDenied = false;

export async function getCurrentLocation(): Promise<ClientLocation | null> {
  if (permanentlyDenied) return null;
  if (cache && Date.now() - cache.at < TTL_MS) return cache.value;

  const perm = await Location.requestForegroundPermissionsAsync();
  if (perm.status !== "granted") {
    if (!perm.canAskAgain) permanentlyDenied = true;
    return null;
  }

  const pos = await Promise.race([
    Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
    new Promise<null>((r) => setTimeout(() => r(null), TIMEOUT_MS)),
  ]);
  if (!pos) return null;

  const value: ClientLocation = {
    lat: pos.coords.latitude,
    lng: pos.coords.longitude,
  };
  cache = { value, at: Date.now() };
  return value;
}
