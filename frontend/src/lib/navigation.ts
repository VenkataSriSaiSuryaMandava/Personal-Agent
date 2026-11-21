import {
  LayoutDashboard,
  MessageSquare,
  ListTodo,
  BriefcaseBusiness,
  Mail,
  CalendarDays,
  Search,
  Code2,
  Globe,
  Brain,
  ShieldCheck,
  Settings,
} from "lucide-react";

export const navigation = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "chat", label: "AI Assistant", icon: MessageSquare },
  { id: "tasks", label: "Tasks", icon: ListTodo },
  { id: "jobs", label: "Job Search", icon: BriefcaseBusiness },
  { id: "email", label: "Email", icon: Mail },
  { id: "calendar", label: "Calendar", icon: CalendarDays },
  { id: "research", label: "Research", icon: Search },
  { id: "coding", label: "Coding", icon: Code2 },
  { id: "browser", label: "Browser", icon: Globe },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "approvals", label: "Approvals", icon: ShieldCheck },
  { id: "settings", label: "Settings", icon: Settings },
] as const;

export type Workspace = (typeof navigation)[number]["id"];
