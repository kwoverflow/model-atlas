"use strict";
const { statSync } = require("node:fs");
const { resolve } = require("node:path");

// Local security patch: lint project roots are explicit paths, never glob input.
function resolveRoot(rootDir, cwd) {
    if (!rootDir || rootDir.length > 4096 || /[*?{}\[\]!\0]/.test(rootDir)) {
        throw new Error("Next lint rootDir requires an explicit directory path (no glob patterns)");
    }
    const directory = resolve(cwd, rootDir);
    try {
        return statSync(directory).isDirectory() ? [directory] : [];
    } catch (error) {
        if (error.code === "ENOENT" || error.code === "ENOTDIR") return [];
        throw error;
    }
}

function getRootDirs(context) {
    const cwd = context.cwd;
    const rootDir = (context.settings.next || {}).rootDir;
    if (typeof rootDir === "string") return resolveRoot(rootDir, cwd);
    if (Array.isArray(rootDir)) {
        if (rootDir.length > 128) throw new Error("Too many explicit Next lint roots");
        return rootDir.flatMap((dir) => typeof dir === "string" ? resolveRoot(dir, cwd) : []);
    }
    return [cwd];
}

exports.getRootDirs = getRootDirs;
