// Rough county centroids — a client-side fallback so the public map always has
// a centre even when the incident carries no coordinates.
export const COUNTY_CENTROIDS: Record<string, [number, number]> = {
  台北市: [25.03, 121.56],
  新北市: [25.01, 121.46],
  基隆市: [25.13, 121.74],
  桃園市: [24.99, 121.3],
  新竹市: [24.8, 120.97],
  新竹縣: [24.7, 121.12],
  苗栗縣: [24.56, 120.82],
  台中市: [24.15, 120.68],
  彰化縣: [24.05, 120.52],
  南投縣: [23.91, 120.69],
  雲林縣: [23.71, 120.43],
  嘉義市: [23.48, 120.45],
  嘉義縣: [23.46, 120.29],
  台南市: [23.0, 120.2],
  高雄市: [22.63, 120.3],
  屏東縣: [22.55, 120.55],
  宜蘭縣: [24.7, 121.74],
  花蓮縣: [23.99, 121.6],
  台東縣: [22.79, 121.11],
  澎湖縣: [23.57, 119.58],
  金門縣: [24.43, 118.32],
  連江縣: [26.16, 119.95],
};

export const TAIWAN_CENTER: [number, number] = [23.75, 121.0];

export function centroidFor(county?: string | null): [number, number] | null {
  if (!county) return null;
  return COUNTY_CENTROIDS[county.replace(/臺/g, "台").trim()] ?? null;
}


/** Great-circle distance in metres. */
export function haversineM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
