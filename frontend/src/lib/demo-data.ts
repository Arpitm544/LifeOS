import type { Preferences, Task } from "./types";

export const defaultPreferences: Preferences = {
  name: "Arpit Maurya", timezone: "Asia/Kolkata", workStart: "09:00", workEnd: "18:00",
  quietStart: "22:30", quietEnd: "07:30", focusStart: "09:00", focusEnd: "11:00",
  protectedEvenings: true, estimatePadding: false, reducedMotion: false,
};

export const demoTasks: Task[] = [
  { id: "report", title: "Finish DBMS report", deadline: "2026-11-20T18:29:00.000Z", effort: 180, importance: 5, category: "study", completed: false },
  { id: "quiz", title: "Prepare for the ML quiz", deadline: "2026-11-16T12:30:00.000Z", effort: 90, importance: 4, category: "study", completed: false },
  { id: "portfolio", title: "Review portfolio case study", deadline: "2026-11-17T12:30:00.000Z", effort: 45, importance: 3, category: "work", completed: false },
  { id: "home", title: "Call home", deadline: "2026-11-15T13:30:00.000Z", effort: 20, importance: 2, category: "social", completed: false },
  { id: "internship", title: "Explore internship opportunities", deadline: null, effort: 60, importance: 1, category: "work", completed: false },
];

export const completionHistory = [3, 5, 4, 7, 6, 4, 8, 6, 9, 7, 5, 10, 8, 11];
