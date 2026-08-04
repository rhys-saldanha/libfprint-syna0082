// Dump functions that reference a source-path string matching a substring.
// @category Analysis

import java.io.File;
import java.io.PrintWriter;
import java.util.Set;
import java.util.TreeSet;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class DumpFunctionsBySourceString extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "usage: DumpFunctionsBySourceString.java OUTPUT SUBSTRING");
        }

        Set<Function> functions = new TreeSet<>((left, right) ->
            left.getEntryPoint().compareTo(right.getEntryPoint()));
        DataIterator data = currentProgram.getListing().getDefinedData(true);
        while (data.hasNext()) {
            Data item = data.next();
            Object value = item.getValue();
            if (value == null || !value.toString().contains(args[1])) {
                continue;
            }
            for (Reference reference : getReferencesTo(item.getAddress())) {
                Function function = currentProgram.getFunctionManager()
                    .getFunctionContaining(reference.getFromAddress());
                if (function != null) {
                    functions.add(function);
                }
            }
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (PrintWriter writer = new PrintWriter(new File(args[0]), "UTF-8")) {
            for (Function function : functions) {
                DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
                writer.println("/* " + function.getName() + " @ " +
                    function.getEntryPoint() + " */");
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
