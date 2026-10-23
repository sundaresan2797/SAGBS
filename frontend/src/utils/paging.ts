import type { PaginatedData } from "@/types";

/** The server sends at most 100 rows at a time, so keep asking until every page is here. */
export async function fetchAllPages<T>(fetchPage: (page: number) => Promise<PaginatedData<T>>): Promise<T[]> {
  const first = await fetchPage(1);
  let items = first.items;
  for (let page = 2; page <= first.total_pages; page++) {
    items = items.concat((await fetchPage(page)).items);
  }
  return items;
}
