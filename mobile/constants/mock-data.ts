import type { MemoryCard } from "@/lib/types";

const HOUR = 1000 * 60 * 60;
const DAY = HOUR * 24;
const now = Date.now();

export const MOCK_MEMORIES: MemoryCard[] = [
  {
    id: "m1",
    date: new Date(now - HOUR * 2),
    title: "",
    excerpt: "Saw a seagull steal someone's sandwich at the pier. Pure chaos.",
    tags: ["funny", "observation"],
    location: "Pier 39, SF",
    image:
      "https://images.unsplash.com/photo-1497935586351-b67a49e012bf?auto=format&fit=crop&q=80&w=800",
  },
  {
    id: "m2",
    date: new Date(now - HOUR * 5),
    title: "",
    excerpt: "Finally figured out the logic bug. Felt a huge sense of relief.",
    tags: ["work"],
    location: "Office",
  },
  {
    id: "m3",
    date: new Date(now - DAY),
    title: "",
    excerpt: "Finished the novel. The ending left me staring at the wall.",
    tags: ["reading"],
    location: "Home",
    image:
      "https://images.unsplash.com/photo-1512820790803-83ca734da794?auto=format&fit=crop&q=80&w=800",
  },
  {
    id: "m4",
    date: new Date(now - DAY * 2),
    title: "",
    excerpt: "Quiet coffee at Elma's. Soft light pouring through the window.",
    tags: ["peace"],
    location: "Elma's Cafe, NY",
  },
];
