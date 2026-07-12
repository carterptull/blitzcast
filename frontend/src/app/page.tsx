import { redirect } from "next/navigation";

// Default sport: existing links and bookmarks land on the NFL slate.
export default function Root() {
  redirect("/nfl");
}
