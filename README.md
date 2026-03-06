Graph Orientation Proof Search

This program searches for proof lines for graph orientation constraints using several branching algorithms and forced orientation rules derived from cycle conditions.

The program reads graphs from an adjacency matrix representation and explores orientation branches until contradictions are found or a valid orientation remains.

Input Format

The graph is represented by an adjacency matrix containing only the characters 0 and 1. Each line corresponds to one row of the matrix.

1. no spaces
2. no additional symbols
3. line breaks indicate row boundaries

Example:
0101
1010
0101
1010

Requirements:
1. The matrix must be square.
2. The diagonal entries must be 0. (Simple graph no loop)
3. The matrix must be symmetric (undirected graph).

Input Types: The program supports two types of input.

1. Zip Dataset
A .zip file containing multiple adjacency matrix files. Each file represents one graph.

Example:
--zip graphs.zip

2. Single Graph File
A .txt file containing one adjacency matrix.

Example:
--txt graph.txt

Notice: Just in case you forget to change to --txt since usually we are using .zip, the code is modified and when you are testing 
        a .txt file the "--zip" will still work. No error printed.

Note: Datasets for 6,7,8,9 vertices non-word-representable graphs .zip file are avaliable at Prof. Sergey Kitaev's personal webset
           https://spider-v.science.strath.ac.uk/sergey.kitaev/research.html



Usage

Run the program from the command line.

python3 PATH_TO_CODE \
  --zip PATH_TO_DATASET \
  --algorithm ALGORITHM_ID \
  --theorem5 OPTION \
  --pivot VALUE \
  --progress


Parameters
--zip: Path to the dataset.

This can be either:
a .zip file containing multiple graphs
a .txt file containing a single adjacency matrix

Example
--zip graphs.zip
or
--zip graph.txt
--algorithm

Branching strategy used for selecting edges.
Available algorithms:1, 2, 3, 4, 5, 6.

Example
--algorithm 1
--theorem5

Controls whether Theorem 5 constraints are applied.

Available options:
off : no constraint is applied
source : pivot vertex is forced to be a source
sink : pivot vertex is forced to be a sink

Example
--theorem5 source
--pivot

Specifies the pivot vertex used in Theorem 5.

Notice: This parameter is required if --theorem5 is not off.

Two formats are supported:
Explicit vertex index
--pivot 3
Automatic selection
--pivot auto-max-degree

In this case the vertex with maximum degree is selected automatically.

--progress


The program generates proof lines corresponding to branching steps and forced orientations.

Notes
Vertex numbering in the output starts from 1, while the program internally uses 0-based indexing. Each adjacency matrix file represents one graph.
