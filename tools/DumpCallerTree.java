// Dump a function and its recursive callers from a Ghidra headless project.
// @category Analysis

import java.io.File;
import java.io.PrintWriter;
import java.util.ArrayDeque;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class DumpCallerTree extends GhidraScript {
    private static class Work {
        final Function function;
        final int depth;

        Work(Function function, int depth) {
            this.function = function;
            this.depth = depth;
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "usage: DumpCallerTree.java OUTPUT ADDRESS DEPTH");
        }
        int maximumDepth = Integer.parseInt(args[2]);
        if (maximumDepth < 0 || maximumDepth > 12) {
            throw new IllegalArgumentException("depth must be between 0 and 12");
        }

        Address address = currentProgram.getAddressFactory().getAddress(args[1]);
        Function root = address == null ? null : currentProgram.getFunctionManager()
            .getFunctionContaining(address);
        if (root == null) {
            throw new IllegalArgumentException("no function contains " + args[1]);
        }

        Map<Function, Integer> functions = new LinkedHashMap<>();
        ArrayDeque<Work> pending = new ArrayDeque<>();
        pending.add(new Work(root, 0));
        while (!pending.isEmpty()) {
            Work work = pending.removeFirst();
            Integer previous = functions.get(work.function);
            if (previous != null && previous <= work.depth) {
                continue;
            }
            functions.put(work.function, work.depth);
            if (work.depth == maximumDepth) {
                continue;
            }
            Set<Function> callers = new TreeSet<>((left, right) ->
                left.getEntryPoint().compareTo(right.getEntryPoint()));
            callers.addAll(work.function.getCallingFunctions(monitor));
            for (Function caller : callers) {
                pending.addLast(new Work(caller, work.depth + 1));
            }
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (PrintWriter writer = new PrintWriter(new File(args[0]), "UTF-8")) {
            for (Map.Entry<Function, Integer> item : functions.entrySet()) {
                Function function = item.getKey();
                writer.println("/* caller-depth " + item.getValue() + ": " +
                    function.getName() + " @ " + function.getEntryPoint() + " */");
                DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
                if (!result.decompileCompleted()) {
                    writer.println("/* Decompilation failed: " +
                        result.getErrorMessage() + " */");
                } else {
                    writer.println(result.getDecompiledFunction().getC());
                }
            }
        } finally {
            decompiler.dispose();
        }
    }
}
