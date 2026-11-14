export const categories = ["study", "work", "errand", "health", "social", "finance", "home", "other"] as const;
export type Category = (typeof categories)[number];
export type Task = {
  id: string;
  title: string;
  deadline: string | null;
  effort: number;
  importance: number;
  category: Category;
  completed: boolean;
};
export type TaskInput = Omit<Task, "id" | "completed">;
export type Preferences = {
  name: string;
  timezone: string;
  workStart: string;
  workEnd: string;
  quietStart: string;
  quietEnd: string;
  focusStart: string;
  focusEnd: string;
  protectedEvenings: boolean;
  estimatePadding: boolean;
  reducedMotion: boolean;
};
