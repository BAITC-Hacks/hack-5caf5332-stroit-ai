import { getCityData } from "./city-data";
const data = await getCityData();
for (const value of Object.values(data))
  console.log(
    JSON.stringify({
      source: value.id,
      status: value.status,
      observedAt: value.observedAt,
      data: value.data,
    }),
  );
