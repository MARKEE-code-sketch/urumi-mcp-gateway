import chat from "../assets/icons/chat-circle-dots.svg?no-inline";
import servers from "../assets/icons/plug.svg?no-inline";
import members from "../assets/icons/users-three.svg?no-inline";
import keys from "../assets/icons/key.svg?no-inline";
import audit from "../assets/icons/list-checks.svg?no-inline";
import arrow from "../assets/icons/arrow-up-right.svg?no-inline";
import send from "../assets/icons/arrow-up.svg?no-inline";
import packageIcon from "../assets/icons/package.svg?no-inline";
import orders from "../assets/icons/receipt.svg?no-inline";
import inventory from "../assets/icons/stack.svg?no-inline";
import check from "../assets/icons/check-circle.svg?no-inline";
import book from "../assets/icons/book-open.svg?no-inline";
import logout from "../assets/icons/sign-out.svg?no-inline";
import shield from "../assets/icons/shield-check.svg?no-inline";
import chevron from "../assets/icons/caret-right.svg?no-inline";
import down from "../assets/icons/caret-down.svg?no-inline";
import plus from "../assets/icons/plus.svg?no-inline";
import close from "../assets/icons/x.svg?no-inline";
import copy from "../assets/icons/copy.svg?no-inline";
import search from "../assets/icons/magnifying-glass.svg?no-inline";
import menu from "../assets/icons/list.svg?no-inline";
import external from "../assets/icons/arrow-square-out.svg?no-inline";

const icons = { chat, servers, members, keys, audit, arrow, send, package: packageIcon, orders, inventory, check, book, logout, shield, chevron, down, plus, close, copy, search, menu, external };
export type IconName = keyof typeof icons;

export function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  return <img src={icons[name]} className={`icon ${className}`} alt="" aria-hidden="true" />;
}

