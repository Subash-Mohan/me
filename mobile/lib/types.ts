export type MessageSender = "user" | "ai";

export type Message = {
  id: string;
  sender: MessageSender;
  text: string;
  images?: string[];
  timestamp: Date;
  memoryAdded?: MemoryCard;
};

export type MemoryCard = {
  id: string;
  date: Date;
  title: string;
  excerpt: string;
  image?: string;
  images?: string[];
  tags: string[];
  location?: string;
};
